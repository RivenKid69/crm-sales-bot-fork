import {
  BaseEntity,
  Column,
  CreateDateColumn,
  Entity,
  JoinColumn,
  ManyToOne,
  PrimaryGeneratedColumn,
  UpdateDateColumn,
} from 'typeorm';
import { AccountDao } from './account.dao';

@Entity('account_transactions')
export class AccountTransactionDao extends BaseEntity {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ name: 'account_id' })
  account_id: number;

  @Column({ name: 'raw_info', type: 'jsonb' })
  raw_info: string;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @UpdateDateColumn({ name: 'updated_at' })
  updated_at: Date;

  @Column()
  provider: string;

  @Column({ name: 'txn_id' })
  txn_id: number;

  @Column({ type: 'numeric', precision: 10, scale: 2 })
  sum: number;

  @Column({ type: 'integer', name: 'contracter_id', nullable: true })
  contracter_id: number | null;

  @ManyToOne(() => AccountDao, (account) => account.transactions)
  @JoinColumn({ name: 'account_id' })
  account: AccountDao;
}
